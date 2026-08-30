import { FocusReader } from "@focus/reader-ui";

import { createStandaloneReaderHost } from "./adapters/create-standalone-reader-host";

const readerHost = createStandaloneReaderHost(import.meta.env.VITE_FOCUS_READER_BASE_URL);

export function App() {
  return <FocusReader host={readerHost} />;
}
