export const SHARED_TYPES_GENERATION = "openapi" as const;

export type { paths, components, operations } from "./generated/openapi";

export type OpenApiGeneratedPlaceholder = {
  source: typeof SHARED_TYPES_GENERATION;
  note: "types-will-be-generated-from-apps-api-openapi";
};
