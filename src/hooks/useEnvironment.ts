import { useState, useEffect, useCallback } from 'react';
import { checkEnvironment } from '@/lib/tauri';
import type { EnvCheckResult } from '@/types/conversion';

interface UseEnvironmentReturn {
  status: EnvCheckResult | null;
  loading: boolean;
  error: string | null;
  /** True once at least one check has been attempted (success or failure). */
  everAttempted: boolean;
  recheck: () => Promise<void>;
}

export function useEnvironment(): UseEnvironmentReturn {
  const [status, setStatus] = useState<EnvCheckResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [everAttempted, setEverAttempted] = useState(false);

  const recheck = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await checkEnvironment();
      setStatus(result);
      setEverAttempted(true);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      setEverAttempted(true);
      // Don't clear existing status on transient errors so the UI still shows the last known state
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    recheck();
  }, [recheck]);

  return { status, loading, error, everAttempted, recheck };
}
