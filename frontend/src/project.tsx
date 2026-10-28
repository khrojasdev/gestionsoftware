import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, errorMessage } from "./api";
import { useAuth } from "./auth";
import type { ProjectOverview } from "./types";

const KEY = "trazo.project";

type ProjectState = {
  projects: ProjectOverview[];
  project: ProjectOverview | null;
  projectId: string | null;
  select: (id: string) => void;
  refresh: () => Promise<void>;
  loading: boolean;
  error: string | null;
  /** Bumps after any mutation so open pages can reload. */
  version: number;
  touch: () => void;
};

const ProjectContext = createContext<ProjectState | null>(null);

function stored(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function ProjectProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [projects, setProjects] = useState<ProjectOverview[]>([]);
  const [projectId, setProjectId] = useState<string | null>(stored);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const list = await api.get<ProjectOverview[]>("/projects-overview");
      setProjects(list);
      setError(null);
      setProjectId((current) => {
        if (current && list.some((item) => item.id === current)) return current;
        const preferred = list.find((item) => item.code === "HORIZONTE-CONECTA") ?? list.find((item) => item.has_plan) ?? list[0];
        return preferred?.id ?? null;
      });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (user) void refresh();
  }, [user, refresh]);

  useEffect(() => {
    try {
      if (projectId) localStorage.setItem(KEY, projectId);
    } catch {
      /* ignore */
    }
  }, [projectId]);

  const touch = useCallback(() => {
    setVersion((value) => value + 1);
    void refresh();
  }, [refresh]);

  const value = useMemo<ProjectState>(
    () => ({
      projects,
      project: projects.find((item) => item.id === projectId) ?? null,
      projectId,
      select: (id: string) => {
        setProjectId(id);
        setVersion((v) => v + 1);
      },
      refresh,
      loading,
      error,
      version,
      touch,
    }),
    [projects, projectId, refresh, loading, error, version, touch],
  );
  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useProject(): ProjectState {
  const value = useContext(ProjectContext);
  if (!value) throw new Error("useProject fuera de ProjectProvider");
  return value;
}
