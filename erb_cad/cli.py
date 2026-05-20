from __future__ import annotations
import rich_click as click
from .main import cli as cad_cli

@click.group()
def flow():
    """Flow: The Erb Robot development toolkit."""
    pass

# Nest the CAD CLI under flow
flow.add_command(cad_cli, name="cad")

if __name__ == "__main__":
    flow()
