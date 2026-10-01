export function getServerApiUrl(): string {
  if (typeof window !== "undefined") {
    throw new Error("getServerApiUrl cannot be used in a browser environment.");
  }
  const url = process.env.API_URL;
  if (!url) {
    throw new Error("API_URL environment variable is missing.");
  }
  return url;
}

export function getClientApiUrl(): string {
  if (typeof window === "undefined") {
    throw new Error("getClientApiUrl cannot be used in a server environment.");
  }
  const url = process.env.NEXT_PUBLIC_API_URL;
  if (!url) {
    throw new Error("NEXT_PUBLIC_API_URL environment variable is missing.");
  }
  return url;
}
