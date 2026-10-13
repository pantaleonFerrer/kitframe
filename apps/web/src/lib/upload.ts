export async function uploadViaPresign(
  file: File,
  purpose: string = "asset_version",
): Promise<string> {
  const { api } = await import("@/lib/api");
  const presign = await api<{ storage_key: string; upload_url: string }>("/uploads/presign", {
    method: "POST",
    body: JSON.stringify({
      purpose,
      file_name: file.name,
      content_type: file.type || "image/jpeg",
      size: file.size,
    }),
  });
  const put = await fetch(presign.upload_url, {
    method: "PUT",
    headers: { "Content-Type": file.type || "image/jpeg" },
    body: file,
  });
  if (!put.ok) {
    throw new Error(`Falló la subida (${put.status})`);
  }
  return presign.storage_key;
}
