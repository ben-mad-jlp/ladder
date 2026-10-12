// Ladder kit for tracing React code in a differential harness (hand-written support code, never
// generated). Works with any test renderer (@testing-library/react, react-test-renderer).
//
//   import { log, identity, resetTrace, traceJsonl, seedRandom } from "./ladder_runtime";
//   import { RenderProbe, useRenderProbe, TraceBoundary, captureConsole, strict } from "./ladder_react";
//
// Everything records through the runtime's trace, so `ladder check` compares it like any step.
import * as React from "react";
import { identity, log } from "./ladder_runtime";

/** Hook form: call inside a component to record each render under `step`, with a render count and
 *  the identity (or value) of what you pass. Identity shows "same object" vs "new object" per render. */
export function useRenderProbe(step: string, value?: unknown, opts: { byValue?: boolean } = {}): void {
  const count = React.useRef(0);
  count.current += 1;
  log(step, { render: count.current, value: value === undefined ? null : opts.byValue ? value : identity(value) });
}

/** Component form: renders `children(value)` from a hook or context and records each render.
 *  <RenderProbe step="ctx.1" use={() => useAuthStore()} /> */
export function RenderProbe<T>(props: { step: string; use: () => T; byValue?: boolean; children?: (v: T) => React.ReactNode }) {
  const v = props.use();
  useRenderProbe(props.step, v, { byValue: props.byValue });
  return <>{props.children ? props.children(v) : null}</>;
}

/** Records a render-time throw (name and message) under `step` and renders nothing instead, so a
 *  harness can observe "this hook throws when given nothing" without crashing the run. */
export class TraceBoundary extends React.Component<{ step: string; children?: React.ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: unknown) {
    log(this.props.step, { threw: error instanceof Error ? `${error.name}: ${error.message}` : String(error) });
  }
  render() { return this.state.failed ? null : this.props.children; }
}

/** Records console output as behavior (tests often count console.warn). Returns a restore function.
 *  Objects in the arguments are recorded by value; pass `quiet: false` to also print them. */
export function captureConsole(step = "console", methods: Array<"log" | "warn" | "error" | "info"> = ["warn", "error"],
                               opts: { quiet?: boolean } = {}): () => void {
  const saved = methods.map((m) => [m, console[m]] as const);
  for (const m of methods) {
    const original = console[m];
    console[m] = (...args: unknown[]) => {
      log(step, { method: m, args: args.map((a) => (a instanceof Error ? `${a.name}: ${a.message}` : a)) });
      if (opts.quiet === false) original.apply(console, args);
    };
  }
  return () => { for (const [m, fn] of saved) console[m] = fn; };
}

/** Wrap an element in StrictMode (development double render and double effects), to compare both ways. */
export function strict(el: React.ReactElement): React.ReactElement {
  return <React.StrictMode>{el}</React.StrictMode>;
}
