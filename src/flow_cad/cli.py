from __future__ import annotations
import rich_click as click
from .main import cli as cad_cli
from .registry_cli import registry as registry_cli

@click.group()
def flow():
    """Flow CAD development toolkit."""
    pass

# Nest the CAD CLI under flow
flow.add_command(cad_cli, name="cad")
flow.add_command(registry_cli, name="registry")

if __name__ == "__main__":
    flow()
