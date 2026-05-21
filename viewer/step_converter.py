#!/usr/bin/env python3
"""
STEP File Converter Server for Flow CAD 3D Viewer

A lightweight FastAPI server that converts STEP files to STL format
for browser-based viewing via Three.js.

Usage:
    python step_converter.py [--host HOST] [--port PORT]

Default: http://localhost:8765
"""

import io
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
import uvicorn

# Add parent directory to path for imports if needed
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    import cadquery as cq
except ImportError:
    print("Error: cadquery is required. Install with: pip install cadquery")
    sys.exit(1)

app = FastAPI(
    title="Flow CAD STEP Converter",
    description="Converts STEP files to STL for Three.js viewer",
    version="1.0.0"
)

# Configuration
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8765
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB max


def convert_step_to_stl(step_data: bytes) -> bytes:
    """
    Convert STEP file data to STL format using cadquery.
    
    Args:
        step_data: Raw STEP file bytes
        
    Returns:
        STL file bytes (binary)
    """
    try:
        # Import the STEP file into cadquery
        # Use importShape with the STEP format
        assembly = cq.importers.importStep(io.BytesIO(step_data))
        
        # Handle both single shapes and assemblies
        if isinstance(assembly, cq.Assembly):
            # For assemblies, we need to extract all solids
            solids = []
            for obj in assembly.objects:
                if hasattr(obj, 'solid') and obj.solid:
                    # Transform the solid by the object's placement
                    transformed = obj.solid.located(obj.placement)
                    solids.append(transformed)
            
            if not solids:
                raise ValueError("No solids found in STEP assembly")
            
            # Combine all solids into a single compound
            combined = cq.Workplane().add(solids[0])
            for solid in solids[1:]:
                combined = combined.add(solid)
            shape = combined.val()
        elif isinstance(assembly, (cq.Solid, cq.Compound, cq.Shell)):
            shape = assembly
        else:
            raise ValueError(f"Unsupported type imported from STEP: {type(assembly)}")
        
        # Export as binary STL
        output = io.BytesIO()
        shape.exportStl(output)
        return output.getvalue()
        
    except Exception as e:
        raise RuntimeError(f"Failed to convert STEP to STL: {e}")


@app.get("/")
def root():
    """Health check and API info."""
    return {
        "service": "Flow CAD STEP Converter",
        "status": "running",
        "endpoints": {
            "/convert": "POST - Convert uploaded STEP file to STL",
            "/health": "GET - Health check"
        }
    }


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "step-converter"}


@app.post("/convert")
async def convert_step(
    file: UploadFile = File(..., description="STEP file to convert")
):
    """
    Convert a STEP file to STL format.
    
    Accepts a .step or .stp file and returns the equivalent .stl file
    as binary data for direct use in Three.js STLLoader.
    """
    # Validate file extension
    filename = (file.filename or "upload").lower()
    if not (filename.endswith('.step') or filename.endswith('.stp')):
        raise HTTPException(
            status_code=400,
            detail="File must be a STEP file (.step or .stp)"
        )
    
    # Read file content
    try:
        step_data = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {e}")
    
    # Check file size
    if len(step_data) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB"
        )
    
    # Convert STEP to STL
    try:
        stl_data = convert_step_to_stl(step_data)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Conversion failed: {e}"
        )
    
    # Return STL data
    return StreamingResponse(
        io.BytesIO(stl_data),
        media_type="application/vnd.ms-pki.stp",
        headers={
            "Content-Disposition": f'attachment; filename="{Path(filename).stem}.stl"'
        }
    )


def main():
    """Main entry point for the converter server."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Flow CAD STEP Converter Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python step_converter.py                    # Default: localhost:8765
  python step_converter.py --host 0.0.0.0     # Listen on all interfaces
  python step_converter.py --port 8080         # Use port 8080
        """
    )
    parser.add_argument(
        "--host",
        type=str,
        default=DEFAULT_HOST,
        help=f"Host to bind to (default: {DEFAULT_HOST})"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port to listen on (default: {DEFAULT_PORT})"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development"
    )
    
    args = parser.parse_args()
    
    print(f"\n{'='*50}")
    print("Flow CAD STEP Converter Server")
    print(f"{'='*50}")
    print(f"Starting server at http://{args.host}:{args.port}")
    print(f"Max file size: {MAX_FILE_SIZE // (1024*1024)}MB")
    print(f"\nEndpoints:")
    print(f"  GET  /       - Health check & API info")
    print(f"  GET  /health - Simple health check")
    print(f"  POST /convert - Convert STEP to STL")
    print(f"\nPress Ctrl+C to stop\n")
    
    uvicorn.run(
        "step_converter:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )


if __name__ == "__main__":
    main()
