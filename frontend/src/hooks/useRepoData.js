import { useState, useEffect, useCallback } from 'react';
import { apiClient } from '@/api/client';

export function useRepo(repoId) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchRepo = useCallback(async () => {
    if (!repoId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.getRepo(repoId);
      setData(res);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [repoId]);

  useEffect(() => {
    fetchRepo();
  }, [fetchRepo]);

  return { data, loading, error, retry: fetchRepo };
}
