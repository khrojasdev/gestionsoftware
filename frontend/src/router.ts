/** Minimal hash router: `#/pagina` or `#/pagina/parametro`, with optional `?query`. */

import { useEffect, useState } from "react";

export type Route = { page: string; param: string | null; query: URLSearchParams };

function parse(): Route {
  const raw = window.location.hash.replace(/^#\/?/, "");
  const [path, queryString = ""] = raw.split("?");
  const [page = "", param = null] = path.split("/").filter(Boolean);
  return { page: page || "proyectos", param: param ? decodeURIComponent(param) : null, query: new URLSearchParams(queryString) };
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(parse);
  useEffect(() => {
    const listener = () => setRoute(parse());
    window.addEventListener("hashchange", listener);
    return () => window.removeEventListener("hashchange", listener);
  }, []);
  return route;
}

export function go(page: string, param?: string | null, query?: Record<string, string>): void {
  const qs = query ? `?${new URLSearchParams(query).toString()}` : "";
  window.location.hash = `/${page}${param ? `/${encodeURIComponent(param)}` : ""}${qs}`;
}

export function href(page: string, param?: string | null): string {
  return `#/${page}${param ? `/${encodeURIComponent(param)}` : ""}`;
}
