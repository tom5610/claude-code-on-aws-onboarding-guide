"""
Client commands for Claude Code Helper with Amazon Bedrock using Typer.
"""

import os
import json
import boto3
import typer
import jinja2
from typing import Dict, List, Any
from pathlib import Path
from botocore.exceptions import ClientError
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt
from rich.panel import Panel

# Create Typer app for client commands
app = typer.Typer(help="Client commands for AWS Bedrock setup")
console = Console()

def get_bedrock_client(service_name="bedrock"):
    """Create a boto3 client for Amazon Bedrock."""
    return boto3.client(service_name)



def list_application_inference_profiles(tag_filters: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    List application inference profiles that match the specified tag filters.

    Args:
        tag_filters: Dictionary of tag keys and values to filter by

    Returns:
        A list of application inference profiles that match the specified tags
    """
    bedrock_client = get_bedrock_client()
    profiles = []

    try:
        # List all application inference profiles
        response = bedrock_client.list_inference_profiles(typeEquals="APPLICATION")

        for profile_summary in response.get('inferenceProfileSummaries', []):
            profile_arn = profile_summary.get('inferenceProfileArn')

            # Get tags about the profile
            tags_on_resource = bedrock_client.list_tags_for_resource(resourceARN=profile_arn)

            # Get tags
            profile_tags = {tag['key']: tag['value'] for tag in tags_on_resource.get('tags', [])}

            # Check if profile has all the required tags
            match = True
            for key, value in tag_filters.items():
                if key not in profile_tags or profile_tags[key] != value:
                    match = False
                    break

            if match:
                profile_info = profile_summary.copy()
                profile_info['tags'] = profile_tags
                profiles.append(profile_info)

        return profiles

    except ClientError as e:
        console.print(f"[bold red]Error listing application inference profiles: {e}[/]")
        return []


def display_inference_profiles(profiles: List[Dict[str, Any]]) -> None:
    """
    Display the application inference profiles in a rich table.

    Args:
        profiles: List of inference profiles to display
    """
    if not profiles:
        console.print("[yellow]No matching application inference profiles found.[/]")
        return

    table = Table(title="Available Application Inference Profiles")
    table.add_column("Index", style="cyan", no_wrap=True)
    table.add_column("Profile Name", style="blue")
    table.add_column("Foundation Model", style="magenta", no_wrap=True)

    # Store profile data for retrieval
    profile_data = []

    for i, profile in enumerate(profiles):
        profile_name = profile.get('inferenceProfileName', 'Unknown')
        model_source = profile.get('models', [{"modelArn": "Unknown"}])[0]["modelArn"]
        model_id = model_source.split('/')[-1] if '/' in model_source else model_source

        table.add_row(str(i+1), profile_name, model_id)
        profile_data.append(profile)

    console.print(table)

    return profile_data


def display_profile_details(profile: Dict[str, Any]) -> str:
    """
    Display detailed information about an application inference profile.

    Args:
        profile: Dictionary containing the profile information

    Returns:
        The ARN of the profile
    """
    profile_name = profile.get('inferenceProfileName', 'Unknown')
    profile_arn = profile.get('inferenceProfileArn', 'Unknown')
    model_source = profile.get('models', [{"modelArn": "Unknown"}])[0]["modelArn"]
    model_id = model_source.split('/')[-1] if '/' in model_source else model_source

    # Display profile information
    console.print(f"\n[bold cyan]===== PROFILE DETAILS =====[/]")

    profile_table = Table(show_header=False)
    profile_table.add_column("Property", style="green")
    profile_table.add_column("Value", style="yellow", no_wrap=True)

    profile_table.add_row("Profile Name", profile_name)
    profile_table.add_row("Foundation Model", model_id)
    profile_table.add_row("ARN", profile_arn)

    # Display profile tags
    tags = profile.get('tags', {})
    if tags:
        profile_table.add_row("Tags", "")
        for key, value in tags.items():
            profile_table.add_row(f"  - {key}", value)

    console.print(profile_table)

    return profile_arn


def write_claude_settings(profile_arn: str, region: str, aws_profile: str) -> None:
    """
    Write Claude settings to the ~/.claude/settings.json file using the template.

    Args:
        profile_arn: The application inference profile ARN
        region: The AWS region
        aws_profile: AWS Profile 
    """
    # Get the path to the template file
    current_dir = Path(__file__).parent.parent
    template_path = current_dir / "template.settings.json"

    # Create ~/.claude directory if it doesn't exist
    claude_dir = os.path.expanduser("~/.claude")
    if not os.path.exists(claude_dir):
        os.makedirs(claude_dir)

    # Read the template file
    try:
        with open(template_path, 'r') as f:
            template_content = f.read()

        # Set up Jinja2 environment for rendering the template
        template = jinja2.Template(template_content)
        rendered_content = template.render({
            'AWS_PROFILE': aws_profile,
            'ANTHROPIC_MODEL': profile_arn,
            'ANTHROPIC_DEFAULT_HAIKU_MODEL': "",
            'AWS_REGION': region
        })

        # Write the rendered template to settings.json
        settings_file = os.path.join(claude_dir, "example.settings.json")
        with open(settings_file, 'w') as f:
            f.write(rendered_content)

        console.print(f"[bold green]Settings written to {settings_file}[/]")

    except (FileNotFoundError, IOError) as e:
        console.print(f"[bold red]Error reading template or writing settings: {e}[/]")
        raise typer.Exit(code=1)

def parse_tags(tags: str) -> dict:
    console.print(f"{tags=}")
    try:
        tags_dict = json.loads(tags)
    except json.JSONDecodeError:
        # in case single quote is being used
        try:
            tags_dict = ast.literal_eval(tags)
        except (ValueError, SyntaxError) as err:
            console.print("[bold red]Error: Tags must be a valid JSON string[/]")
            raise typer.Exit(code=1)
    return tags_dict

@app.command("setup")
def client_setup(
    tags: str = typer.Option(..., "--tags", help="JSON string with resource tags")
):
    """
    Set up Claude Code client with the correct application inference profile and API key.

    This command:
    1. Finds the tags for the specified IAM user
    2. Finds application inference profiles matching those tags
    3. Allows selection of a profile and displays its ARN
    4. Prompts for AWS region
    5. Creates or resets an API key for Amazon Bedrock
    6. Configures the Claude Code settings file
    """
     # Parse JSON tags
    tags_dict = parse_tags(tags)

    # Validate required tags
    if not tags_dict:
        console.print("[bold red]Error: Tags must not be empty.[/]")
        raise typer.Exit(code=1)

    # Step 2: Find matching application inference profiles
    with console.status("Finding matching application inference profiles..."):
        profiles = list_application_inference_profiles(tags_dict)

    if not profiles:
        console.print(f"[bold yellow]No application inference profiles found matching the user's tags.[/]")
        raise typer.Exit(code=1)

    # Step 3: Display profiles and allow selection
    console.print(f"\n[bold]Available Application Inference Profiles:[/]")
    profile_data = display_inference_profiles(profiles)

    try:
        choice = int(Prompt.ask("\nEnter the number of the profile to use", default="1"))
        if 1 <= choice <= len(profile_data):
            selected_profile = profile_data[choice - 1]
            profile_arn = display_profile_details(selected_profile)
        else:
            console.print(f"[bold red]Invalid choice. Please choose a number between 1 and {len(profile_data)}.[/]")
            raise typer.Exit(code=1)
    except ValueError:
        console.print("[bold red]Invalid input. Please enter a number.[/]")
        raise typer.Exit(code=1)

    # Step 4: Ask for AWS region
    region = Prompt.ask("Enter AWS region", default="us-east-1")

    # Step 5: Ask for AWS profile
    aws_profile = Prompt.ask("Enter AWS Profile")

    # Step 6: Write settings file
    with console.status("Writing Claude Code settings file..."):
        write_claude_settings(profile_arn, region, aws_profile)

    # Final success message
    console.print(Panel.fit(
        "[bold green]Claude Code client setup complete![/]\n\n"
        f"Your Claude Code is now configured to use:\n"
        f"  • AWS Profile: {aws_profile}\n"
        f"  • Region: {region}\n"
        f"  • Profile ARN: {profile_arn}\n\n"
        "You can now use Claude Code with Amazon Bedrock.",
        title="Setup Complete",
        border_style="green"
    ))


if __name__ == "__main__":
    app()