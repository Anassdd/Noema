import { useRef, useState } from "react";

// Whole-area file drag-and-drop. Reacts only to file drags (not text/selection)
// and uses a depth counter so dragging over child elements doesn't flicker the
// overlay. Calls `onFile(file)` with the first dropped file. Spread the returned
// `dropHandlers` onto the drop zone; render an overlay while `dragActive`.
export function useFileDrop(onFile) {
  const [dragActive, setDragActive] = useState(false);
  const depth = useRef(0);

  const hasFiles = (e) => e.dataTransfer?.types?.includes("Files");

  const dropHandlers = {
    onDragEnter: (e) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth.current += 1;
      setDragActive(true);
    },
    onDragOver: (e) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    },
    onDragLeave: (e) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth.current -= 1;
      if (depth.current <= 0) {
        depth.current = 0;
        setDragActive(false);
      }
    },
    onDrop: (e) => {
      e.preventDefault();
      depth.current = 0;
      setDragActive(false);
      const file = e.dataTransfer.files?.[0];
      if (file) onFile(file);
    },
  };

  return { dragActive, dropHandlers };
}
