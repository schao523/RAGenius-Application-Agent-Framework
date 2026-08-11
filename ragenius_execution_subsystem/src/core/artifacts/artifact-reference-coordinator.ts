export interface ArtifactReferenceScope {
  appId: string;
  sessionId: string;
  artifactId: string;
}

function scopeKey(scope: ArtifactReferenceScope): string {
  return `${scope.appId}\u0000${scope.sessionId}\u0000${scope.artifactId}`;
}

export class ArtifactReferenceCoordinator {
  private readonly leases = new Map<string, number>();
  private readonly deletions = new Set<string>();

  acquire(scopes: ArtifactReferenceScope[]): () => void {
    const keys = [...new Set(scopes.map(scopeKey))];
    if (keys.some((key) => this.deletions.has(key))) {
      throw new Error("Artifact deletion is already in progress.");
    }
    for (const key of keys) {
      this.leases.set(key, (this.leases.get(key) ?? 0) + 1);
    }
    let released = false;
    return () => {
      if (released) return;
      released = true;
      for (const key of keys) {
        const remaining = (this.leases.get(key) ?? 1) - 1;
        if (remaining > 0) this.leases.set(key, remaining);
        else this.leases.delete(key);
      }
    };
  }

  isLeased(scope: ArtifactReferenceScope): boolean {
    return (this.leases.get(scopeKey(scope)) ?? 0) > 0;
  }

  async deleteIfUnused<T>(
    scope: ArtifactReferenceScope,
    hasPersistentReference: () => Promise<boolean>,
    deleteArtifact: () => Promise<T>
  ): Promise<{ inUse: true } | { inUse: false; result: T }> {
    const key = scopeKey(scope);
    if (this.deletions.has(key) || this.isLeased(scope)) {
      return { inUse: true };
    }
    this.deletions.add(key);
    try {
      if (await hasPersistentReference()) {
        return { inUse: true };
      }
      return { inUse: false, result: await deleteArtifact() };
    } finally {
      this.deletions.delete(key);
    }
  }
}
