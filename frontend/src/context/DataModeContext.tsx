import { createContext, useContext, useState, useCallback } from "react";

export type DataMode = "MOCK" | "LIVE";

type DataModeContextValue = {
  mode: DataMode;
  setMode: (mode: DataMode) => void;
  toggleMode: () => void;
};

const DataModeContext = createContext<DataModeContextValue | null>(null);

export function DataModeProvider(props: { children: React.ReactNode; initialMode?: DataMode }) {
  const [mode, setModeState] = useState<DataMode>(props.initialMode ?? "MOCK");
  const setMode = useCallback((m: DataMode) => setModeState(m), []);
  const toggleMode = useCallback(
    () => setModeState((prev) => (prev === "MOCK" ? "LIVE" : "MOCK")),
    []
  );
  return (
    <DataModeContext.Provider value={{ mode, setMode, toggleMode }}>
      {props.children}
    </DataModeContext.Provider>
  );
}

export function useDataMode() {
  const ctx = useContext(DataModeContext);
  if (!ctx) throw new Error("useDataMode must be used within DataModeProvider");
  return ctx;
}
