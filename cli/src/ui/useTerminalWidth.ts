import { useEffect, useState } from "react";
import { useStdout } from "ink";

export function useTerminalWidth(): number {
  const { stdout } = useStdout();
  const [width, setWidth] = useState(stdout.columns || 80);
  useEffect(() => {
    const resize = () => setWidth(stdout.columns || 80);
    stdout.on("resize", resize);
    return () => { stdout.off("resize", resize); };
  }, [stdout]);
  return width;
}
