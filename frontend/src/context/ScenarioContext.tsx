/**
 * Phase 8.5: Scenario context for MOCK mode — current scenario key, bundle, and validation warnings.
 * Selection persisted in localStorage. Only used when mode === "MOCK".
 */
import { createContext, useContext, useState, useCallback, useMemo } from "react";
import type { ScenarioBundle } from "@/types/views";
import type { ScenarioKey } from "@/mock/scenarios";
import { getScenarioBundle, getDefaultScenarioKey, SCENARIO_KEYS } from "@/mock/scenarios";
import { validateScenarioBundle } from "@/mock/validator";
import type { ValidationWarning } from "@/mock/validator";

const STORAGE_KEY = "chakraops_mock_scenario";

function loadStoredScenarioKey(): ScenarioKey {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && SCENARIO_KEYS.includes(stored as ScenarioKey)) return stored as ScenarioKey;
  } catch {
    /* ignore */
  }
  return getDefaultScenarioKey();
}

type ScenarioContextValue = {
  scenarioKey: ScenarioKey;
  setScenarioKey: (key: ScenarioKey) => void;
  bundle: ScenarioBundle;
  warnings: ValidationWarning[];
  scenarioKeys: readonly ScenarioKey[];
};

const ScenarioContext = createContext<ScenarioContextValue | null>(null);

export function ScenarioProvider(props: { children: React.ReactNode }) {
  const [scenarioKey, setScenarioKeyState] = useState<ScenarioKey>(loadStoredScenarioKey);

  const setScenarioKey = useCallback((key: ScenarioKey) => {
    setScenarioKeyState(key);
    try {
      localStorage.setItem(STORAGE_KEY, key);
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo(() => {
    const bundle = getScenarioBundle(scenarioKey);
    const warnings = validateScenarioBundle(bundle, scenarioKey);
    return {
      scenarioKey,
      setScenarioKey,
      bundle,
      warnings,
      scenarioKeys: SCENARIO_KEYS,
    };
  }, [scenarioKey, setScenarioKey]);

  return (
    <ScenarioContext.Provider value={value}>
      {props.children}
    </ScenarioContext.Provider>
  );
}

export function useScenario() {
  const ctx = useContext(ScenarioContext);
  return ctx;
}
