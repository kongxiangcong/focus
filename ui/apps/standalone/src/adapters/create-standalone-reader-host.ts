import type { ReaderHost } from "@focus/reader-contracts";

import { FixtureReaderHost } from "./fixture-reader-host";
import { HttpReaderHost } from "./http-reader-host";

export function createStandaloneReaderHost(baseUrl?: string): ReaderHost {
  const normalized = baseUrl?.trim();
  return normalized ? new HttpReaderHost({ baseUrl: normalized }) : new FixtureReaderHost();
}
