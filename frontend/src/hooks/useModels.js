import { useEffect, useState } from "react";

import { fetchModels } from "../api/models.js";

// Available chat models + the current selection (session-wide). Re-fetchable
// because the one-shot load can fail silently if the page opens during a
// backend restart (uvicorn --reload), which left the selector blank.
export function useModels() {
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState("");

  const loadModels = () =>
    fetchModels()
      .then(({ models: list, default: def }) => {
        // Make sure the default is always selectable, even if not listed.
        const full = def && !list.includes(def) ? [def, ...list] : list;
        setModels(full);
        setSelectedModel((cur) => cur || def || full[0] || "");
      })
      .catch(console.error);

  useEffect(() => {
    loadModels();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { models, selectedModel, setSelectedModel, loadModels };
}
