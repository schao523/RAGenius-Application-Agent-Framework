import { z } from "zod";

const exactHostSchema = z.string().trim().min(1).max(253).superRefine((value, ctx) => {
  if (!/^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/.test(value) || value.includes("..")) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: "Expected an exact lowercase ASCII host." });
  }
});

const managedTargetSchema = z.object({
  id: z.string().trim().min(1).max(100),
  label: z.string().trim().min(1).max(200),
  launch: z.discriminatedUnion("kind", [
    z.object({
      kind: z.literal("https_url"),
      url: z.string().url()
    }).strict(),
    z.object({
      kind: z.literal("provider_window"),
      provider: z.literal("computer_use"),
      application: z.string().trim().min(1).max(200)
    }).strict()
  ]),
  allowedHosts: z.array(exactHostSchema).max(20),
  verifierId: z.string().trim().min(1).max(100)
}).strict();

type ParsedManagedAuthenticationTarget = z.infer<typeof managedTargetSchema>;

export type CodexManagedAuthenticationTarget = Readonly<
  Omit<ParsedManagedAuthenticationTarget, "allowedHosts" | "launch"> & {
    allowedHosts: readonly string[];
    launch: Readonly<ParsedManagedAuthenticationTarget["launch"]>;
  }
>;

export interface ManagedAuthenticationVerificationInput {
  executionId: string;
  target: CodexManagedAuthenticationTarget;
}

export interface ManagedAuthenticationVerifier {
  readonly id: string;
  verify(input: ManagedAuthenticationVerificationInput): Promise<{
    verified: boolean;
    diagnosticCode?: string;
  }>;
}

export function parseExactAuthenticationHosts(raw: string): readonly string[] {
  const parsed = z.array(exactHostSchema).max(100).parse(JSON.parse(raw));
  if (new Set(parsed).size !== parsed.length) {
    throw new Error("Authentication host entries must be unique.");
  }
  return Object.freeze(parsed);
}

export function parseCodexManagedAuthenticationTargets(
  raw: string
): readonly CodexManagedAuthenticationTarget[] {
  const parsed = z.array(managedTargetSchema).max(100).parse(JSON.parse(raw));
  if (new Set(parsed.map((target) => target.id)).size !== parsed.length) {
    throw new Error("Managed authentication target ids must be unique.");
  }
  for (const target of parsed) {
    if (target.launch.kind !== "https_url") continue;
    const url = new URL(target.launch.url);
    if (
      url.protocol !== "https:" ||
      url.username ||
      url.password ||
      url.hash ||
      !target.allowedHosts.includes(url.hostname)
    ) {
      throw new Error(`Managed authentication target ${target.id} has an unsafe launch URL.`);
    }
  }
  return Object.freeze(parsed.map((target) => Object.freeze({
    ...target,
    allowedHosts: Object.freeze([...target.allowedHosts]),
    launch: Object.freeze({ ...target.launch })
  })));
}

export function eligibleManagedAuthenticationTargets(
  targets: readonly CodexManagedAuthenticationTarget[],
  verifiers: ReadonlyMap<string, ManagedAuthenticationVerifier>
): readonly CodexManagedAuthenticationTarget[] {
  return Object.freeze(targets.filter((target) => verifiers.has(target.verifierId)));
}
