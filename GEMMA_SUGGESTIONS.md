# GEMMA_SUGGESTIONS.md: From Vibe CAD to Engineering Flow

## The "Vibe CAD" Diagnosis
You are currently operating in a high-velocity prototyping mode where geometry is defined by intuition and verified by visual inspection (or failed prints). This works until the part count hits a critical mass where one change in `ChassisParams` creates a ripple effect of failures across five other parts.

**The current bottleneck:** The 2,046-line monolith (`cad/erb_lower_chassis.py`) is a "black box." You put parameters in, and STEP files come out. If the part doesn't fit, you have to hunt through 2,000 lines of code to find which specific offset caused the clash.

---

## The Gemma Strategy: Parametric Contracts
Instead of a full rewrite (Qwen) or just adding external scripts (Codex), I propose moving toward **Parametric Contracts**. 

A "Contract" is a simple Python function that asserts a mechanical truth about a part *before* it is even built in 3D.

**Example: The Shelf Connectivity Contract**
Instead of checking if the shelf is connected by looking at the STEP file, we write a contract:
`assert (shelf_width / 2) - side_notch_depth > center_channel_width / 2 + min_bridge_thickness`

If this assertion fails, the script crashes *immediately* with a clear error: `"Shelf would be disconnected at X=45mm"`. You fix the number in 2 seconds instead of finding out 20 minutes later in Bambu Studio.

---

## Recommended Engineering Flow (The "Gemma Loop")

I suggest adopting this strict loop for every change:

1. **Define the Contract:** Before changing a dimension, ask: *"What must remain true for this to still work?"* (e.g., "The axle hole must be 2mm from the edge").
2. **Update Params:** Change the value in `ChassisParams`.
3. **Run Headless Validation:** Run a lightweight test suite that checks these contracts (no STEP generation needed).
4. **Targeted Generation:** Generate only the affected parts.
5. **Assembly Check:** Run the interference script to ensure no new clashes.

---

## Immediate Technical Roadmap

### 1. The "Contract" Layer (Low Effort, High Gain)
Don't move the code yet. Just add a `validate_params()` method to `ChassisParams`.
- Every time `P = ChassisParams()` is called, it should run a series of `assert` statements.
- If you set the battery box too wide for the chassis, the script should refuse to run.

### 2. Decouple "Logic" from "Geometry"
The monolith mixes *how* to build a part with *what* the part is.
- **Step A:** Extract all `make_*` functions into a separate file (`cad/geometry_lib.py`).
- **Step B:** Keep `erb_lower_chassis.py` as a simple "Recipe" file that calls those functions and exports them.
- This makes the code readable: the Recipe says *what* to make; the Lib says *how* to make it.

### 3. The "Print Manifest" (The Handoff)
Stop guessing which STEP files are current. Create a `PRINT_MANIFEST.json` that maps:
`Part Name` $\rightarrow$ `STEP Filename` $\rightarrow$ `Last Validated Timestamp`.
If the timestamp is older than the last change to `ChassisParams`, the manifest marks it as **STALE**.

---

## Summary of Agent Roles
To keep us aligned, here is how I see our "Council of Agents" working:
- **Qwen:** The Architect (provides the ideal end-state).
- **Codex:** The Operator (provides the tooling and CI/CD).
- **Gemma (Me):** The Engineer (bridges the gap by turning mechanical requirements into code assertions).

**Next Step Recommendation:** 
I can implement a `validate_params()` method in your current generator right now. This will immediately stop "vibe" errors from reaching your printer. Should I proceed?
