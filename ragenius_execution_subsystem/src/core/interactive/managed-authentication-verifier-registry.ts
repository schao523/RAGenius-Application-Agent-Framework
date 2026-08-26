import type { ManagedAuthenticationVerifier } from "./codex-managed-auth-targets.js";

export class ManagedAuthenticationVerifierRegistry {
  private readonly verifiers: ReadonlyMap<string, ManagedAuthenticationVerifier>;

  constructor(entries: readonly ManagedAuthenticationVerifier[]) {
    const verifiers = new Map<string, ManagedAuthenticationVerifier>();
    for (const verifier of entries) {
      const id = verifier.id.trim();
      if (!id) {
        throw new Error("Managed authentication verifier id cannot be blank.");
      }
      if (verifiers.has(id)) {
        throw new Error(`Duplicate managed authentication verifier id: ${id}`);
      }
      verifiers.set(id, verifier);
    }
    this.verifiers = verifiers;
  }

  get(id: string): ManagedAuthenticationVerifier | undefined {
    return this.verifiers.get(id);
  }

  has(id: string): boolean {
    return this.verifiers.has(id);
  }

  asReadonlyMap(): ReadonlyMap<string, ManagedAuthenticationVerifier> {
    return new Map(this.verifiers);
  }
}
