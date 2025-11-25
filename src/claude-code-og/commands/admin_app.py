"""
Admin commands for Claude Code Helper with Amazon Bedrock using Typer.
"""

import ast
import json
import boto3
import typer
from typing import Dict, List, Any, Optional
from botocore.exceptions import ClientError
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt

# Create Typer app for admin commands
app = typer.Typer(help="Admin commands for AWS Bedrock setup")
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
        response = bedrock_client.list_inference_profiles(maxResults=250, typeEquals="APPLICATION")

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


def list_claude_inference_profiles() -> List[Dict[str, Any]]:
    """
    List all available Claude foundation model inference profiles.
    Only includes Claude models >= 3.7 (excludes Claude 3/3.5 sonnet/haiku/opus models).

    Returns:
        A list of dictionaries containing information about Claude inference profiles.
    """
    bedrock_client = get_bedrock_client()

    try:
        # Get all system-defined inference profiles
        response = bedrock_client.list_inference_profiles(typeEquals="SYSTEM_DEFINED")

        # Filter for Claude models >= 3.7
        claude_profiles = [
            profile for profile in response.get('inferenceProfileSummaries', [])
            if 'claude' in profile.get('inferenceProfileId', '').lower() and
               all(version not in profile.get('inferenceProfileId', '').lower()
                   for version in ['3-5', 'claude-3-haiku', 'claude-3-sonnet', 'claude-3-opus'])
        ]

        claude_profiles = sorted(claude_profiles, key=lambda x: x.get('inferenceProfileId', ''))

        return claude_profiles

    except ClientError as e:
        console.print(f"[bold red]Error listing inference profiles: {e}[/]")
        return []


def display_inference_profiles(profiles: List[Dict[str, Any]]) -> None:
    """
    Display the inference profiles in a rich table.

    Args:
        profiles: List of inference profiles to display
    """
    if not profiles:
        console.print("[yellow]No Claude inference profiles found.[/]")
        return

    table = Table(title="Available Claude Inference Profiles")
    table.add_column("Index", style="cyan", no_wrap=True)
    table.add_column("Profile ID", style="blue", no_wrap=True)
    table.add_column("ARN", no_wrap=False)

    for i, profile in enumerate(profiles):
        profile_id = profile.get('inferenceProfileId', 'Unknown')
        arn = profile.get('inferenceProfileArn', 'Unknown')
        table.add_row(str(i+1), profile_id, arn)

    console.print(table)


def prompt_for_inference_profile() -> Optional[Dict[str, Any]]:
    """
    Prompt the user to select a Claude inference profile.

    Returns:
        The selected inference profile or None if no selection was made.
    """
    profiles = list_claude_inference_profiles()

    if not profiles:
        return None

    display_inference_profiles(profiles)

    try:
        choice = int(Prompt.ask("\nEnter the number of the profile to use", default="1"))
        if 1 <= choice <= len(profiles):
            return profiles[choice - 1]
        else:
            console.print("[bold red]Invalid choice.[/]")
            return None
    except ValueError:
        console.print("[bold red]Invalid input. Please enter a number.[/]")
        return None

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

@app.command("create-aip")
def create_profile(
    name: str = typer.Option(..., "--name", "-n", help="Name of the application inference profile"),
    tags: str = typer.Option(..., "--tags", help="JSON string with resource tags"),
):
    """
    Create an application inference profile for Amazon Bedrock.

    This command:
    1. Lists available Claude foundation model inference profiles
    2. Prompts you to select a profile
    3. Creates an application inference profile using the selected profile
    4. Tags the profile with the specified tags

    The tags parameter must be a JSON string containing at least 'Team' and 'DeveloperId' keys.
    Example: --tags '{"Team": "DevTeam", "DeveloperId": "dev123"}'
    """
    # Parse JSON tags
    tags_dict = parse_tags(tags)

    # Validate required tags
    if not tags_dict:
        console.print("[bold red]Error: Tags must not be empty.[/]")
        raise typer.Exit(code=1)

    # Convert tags dict to AWS format for Bedrock (lowercase key)
    aws_tags = [{"key": k, "value": v} for k, v in tags_dict.items()]

    bedrock_client = get_bedrock_client()

    # Prompt user to select an inference profile
    console.print("[bold blue]Retrieving available Claude foundation model inference profiles...[/]")
    selected_profile = prompt_for_inference_profile()
    if not selected_profile:
        console.print("[bold red]No profile selected. Exiting.[/]")
        raise typer.Exit(code=1)

    inference_profile_id = selected_profile.get('inferenceProfileId')
    inference_profile_arn = selected_profile.get('inferenceProfileArn')

    try:
        console.print(f"\nCreating application inference profile: [bold]{name}[/]")
        console.print(f"Using inference profile: [bold]{inference_profile_arn}[/] (ID: {inference_profile_id})")

        with console.status("Creating profile..."):
            response = bedrock_client.create_inference_profile(
                inferenceProfileName=name,
                description=f"Application Inference Profile {name}",
                modelSource={"copyFrom":inference_profile_arn},
                tags=aws_tags
            )

        app_profile_arn = response.get('inferenceProfileArn')

        # Display application profile information in a table
        table = Table(title="Application Inference Profile")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green", no_wrap=True)

        table.add_row("Name", name)
        table.add_row("ARN", app_profile_arn)
        table.add_row("Inference Profile", inference_profile_id)

        # Display all tags in the table
        tags_str = ", ".join([f"{k}={v}" for k, v in tags_dict.items()])
        table.add_row("Tags", tags_str)

        console.print(table)

        console.print(f"\n[bold green]Application inference profile '{name}' successfully created.[/]")
        console.print(f"[bold]Note:[/] You can now use this profile with the created IAM user to access Claude models.")

    except ClientError as e:
        console.print(f"[bold red]Error creating application inference profile: {e}[/]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()