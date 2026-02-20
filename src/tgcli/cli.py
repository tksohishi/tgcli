from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Annotated, Optional

import typer
from rich.console import Console
from telethon.errors import UnauthorizedError

app = typer.Typer(help="Search and read Telegram messages from the terminal.")
auth_app = typer.Typer(help="Manage Telegram authentication.", invoke_without_command=True)
app.add_typer(auth_app, name="auth")

stdout = Console()
stderr = Console(stderr=True)


@auth_app.callback(invoke_without_command=True)
def auth_default(ctx: typer.Context) -> None:
    """Smart auth: configure, login, or show status as needed."""
    if ctx.invoked_subcommand is not None:
        return

    from tgcli.config import CONFIG_PATH, load_config, write_config
    from tgcli.formatting import format_auth_status

    # Step 1: ensure config exists
    try:
        load_config()
    except SystemExit:
        import webbrowser

        stderr.print(f"No config found at {CONFIG_PATH}\n")
        stderr.print(
            "You need a Telegram API app to use this tool.\n"
            "Create one at: https://my.telegram.org/apps\n"
        )
        if typer.confirm("Open my.telegram.org in your browser?", default=True):
            webbrowser.open("https://my.telegram.org/apps")
        typer.prompt("Press Enter when you have your credentials", default="", show_default=False)
        api_id = typer.prompt("API ID", type=int)
        api_hash = typer.prompt("API Hash", type=str)
        path = write_config(api_id, api_hash)
        stderr.print(f"\nConfig written to {path}\n")
    except Exception as e:
        stderr.print(f"[red]Config error:[/red] {e}")
        stderr.print(f"Check your config at {CONFIG_PATH}")
        raise typer.Exit(1)

    # Step 2: check auth state
    from tgcli.auth import get_status

    try:
        info = asyncio.run(get_status())
    except Exception as e:
        stderr.print(f"[red]Error checking status:[/red] {e}")
        raise typer.Exit(1)

    if info["authenticated"]:
        stdout.print(format_auth_status(**info))
        stdout.print("Run `tg auth logout` to log out.")
        return

    # Step 3: not authenticated, run login
    from tgcli.auth import login as _login

    try:
        asyncio.run(_login())
        stdout.print("[green]Login successful.[/green]")
    except Exception as e:
        stderr.print(f"[red]Login failed:[/red] {e}")
        raise typer.Exit(1)


@auth_app.command()
def login() -> None:
    """Interactive login: phone + verification code (or 2FA password)."""
    from tgcli.auth import login as _login

    try:
        asyncio.run(_login())
        stdout.print("[green]Login successful.[/green]")
    except Exception as e:
        stderr.print(f"[red]Login failed:[/red] {e}")
        raise typer.Exit(1)


@auth_app.command()
def logout() -> None:
    """Remove session from Keychain."""
    from tgcli.auth import logout as _logout

    try:
        asyncio.run(_logout())
        stdout.print("Logged out.")
    except Exception as e:
        stderr.print(f"[red]Logout failed:[/red] {e}")
        raise typer.Exit(1)


@auth_app.command()
def status() -> None:
    """Show current auth state."""
    from tgcli.auth import get_status
    from tgcli.formatting import format_auth_status

    try:
        info = asyncio.run(get_status())
    except SystemExit as e:
        stderr.print(f"[red]Configuration error:[/red] {e}")
        stderr.print("Run `tg auth` to set up.")
        raise typer.Exit(1)
    except Exception as e:
        stderr.print(f"[red]Error checking status:[/red] {e}")
        raise typer.Exit(1)

    stdout.print(format_auth_status(**info))


def _parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


@app.command()
def search(
    query: str,
    chat: Annotated[Optional[str], typer.Option(help="Limit search to a specific chat.")] = None,
    from_user: Annotated[
        Optional[str], typer.Option("--from", help="Filter by sender name.")
    ] = None,
    limit: Annotated[int, typer.Option(help="Max results to return.")] = 20,
    after: Annotated[Optional[str], typer.Option(help="Only messages after this date (YYYY-MM-DD).")] = None,
    before: Annotated[Optional[str], typer.Option(help="Only messages before this date (YYYY-MM-DD).")] = None,
) -> None:
    """Search messages across chats."""
    from tgcli.client import create_client, search_messages
    from tgcli.formatting import format_search_results

    try:
        after_dt = _parse_date(after) if after else None
        before_dt = _parse_date(before) if before else None
    except ValueError as e:
        stderr.print(f"[red]Invalid date format:[/red] {e}")
        stderr.print("Expected format: YYYY-MM-DD")
        raise typer.Exit(1)

    async def _run():
        client = create_client()
        async with client:
            return await search_messages(
                client, query, chat=chat, from_user=from_user,
                limit=limit, after=after_dt, before=before_dt,
            )

    try:
        results = asyncio.run(_run())
    except SystemExit as e:
        stderr.print(f"[red]Configuration error:[/red] {e}")
        stderr.print("Run `tg auth` to set up.")
        raise typer.Exit(1)
    except UnauthorizedError:
        stderr.print("[red]Not authenticated.[/red] Run `tg auth login` first.")
        raise typer.Exit(2)
    except Exception as e:
        stderr.print(f"[red]Search failed:[/red] {e}")
        raise typer.Exit(1)

    if not results:
        stdout.print("No messages found.")
        return

    stdout.print(format_search_results(results))


@app.command()
def thread(
    chat: str,
    message_id: int,
    context: Annotated[int, typer.Option(help="Messages before/after the target.")] = 5,
) -> None:
    """View a message with surrounding context."""
    from tgcli.client import create_client, get_thread_context
    from tgcli.formatting import format_thread

    async def _run():
        client = create_client()
        async with client:
            return await get_thread_context(client, chat, message_id, context=context)

    try:
        messages, target_id, replied_to = asyncio.run(_run())
    except SystemExit as e:
        stderr.print(f"[red]Configuration error:[/red] {e}")
        stderr.print("Run `tg auth` to set up.")
        raise typer.Exit(1)
    except UnauthorizedError:
        stderr.print("[red]Not authenticated.[/red] Run `tg auth login` first.")
        raise typer.Exit(2)
    except Exception as e:
        stderr.print(f"[red]Thread fetch failed:[/red] {e}")
        raise typer.Exit(1)

    if not messages:
        stdout.print("No messages found.")
        return

    stdout.print(format_thread(messages, target_id, replied_to=replied_to))
