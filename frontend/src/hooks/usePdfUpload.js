import { useCallback, useState } from "react";

import { uploadPdf } from "../api/upload.js";

// Upload a PDF, extract its text on the backend, and append it to the active
// conversation's documents. `setDocuments` is that conversation's documents
// updater (multiple PDFs allowed).
export function usePdfUpload(setDocuments) {
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);

  const attachPdf = useCallback(
    async (file) => {
      setUploadError(null);
      setUploading(true);
      try {
        const doc = await uploadPdf(file);
        setDocuments((prev) => [...prev, { id: crypto.randomUUID(), ...doc }]);
      } catch (err) {
        setUploadError(err.message);
      } finally {
        setUploading(false);
      }
    },
    [setDocuments],
  );

  const removeDocument = useCallback(
    (id) => setDocuments((prev) => prev.filter((d) => d.id !== id)),
    [setDocuments],
  );

  return { uploading, uploadError, setUploadError, attachPdf, removeDocument };
}
