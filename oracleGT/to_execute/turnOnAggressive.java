import ghidra.app.util.headless.HeadlessScript;

public class TurnOnAggressive extends HeadlessScript {
	@Override
	public void run() throws Exception {

		/* make sure analysis actually runs */
		enableHeadlessAnalysis(true);          // README lines 97-99 :contentReference[oaicite:0]{index=0}

		/* flip on the aggressive analyzers — note the names have NO “(Prototype)” suffix */
		setAnalysisOption(currentProgram, "Aggressive Instruction Finder", "true");
		setAnalysisOption(currentProgram, "x86 Aggressive Instruction Finder", "true");  // or ARM, MIPS, …

		/* (optional) keep other helpers you turned off earlier */
		setAnalysisOption(currentProgram, "Function Start Search", "true");
	}
}
