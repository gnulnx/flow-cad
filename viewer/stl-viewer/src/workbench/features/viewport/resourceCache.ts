/** Byte-bounded LRU with leases: visible resources cannot be evicted. */
export class ResourceCache<T> {
  private entries = new Map<string, { value: T; bytes: number; users: number }>()
  constructor(readonly budget: number, private dispose: (value: T) => void = () => {}) {}
  get sizeBytes() { return [...this.entries.values()].reduce((sum, entry) => sum + entry.bytes, 0) }
  get(key: string): T | undefined {
    const entry = this.entries.get(key)
    if (!entry) return undefined
    this.entries.delete(key); this.entries.set(key, entry)
    return entry.value
  }
  put(key: string, value: T, bytes: number) {
    const existing = this.entries.get(key)
    if (existing) throw new Error('Cache keys are immutable')
    this.entries.set(key, { value, bytes, users: 0 })
    this.trim()
  }
  retain(key: string): (() => void) | undefined {
    const entry = this.entries.get(key)
    if (!entry) return undefined
    this.get(key); entry.users++
    let released = false
    return () => { if (!released) { released = true; entry.users--; this.trim() } }
  }
  // Insert already leased so oversized visible geometry survives until release.
  lease(key: string, value: T, bytes: number): () => void {
    if (!this.entries.has(key)) this.entries.set(key, { value, bytes, users: 0 })
    const release = this.retain(key)!
    this.trim()
    return release
  }
  clear() {
    for (const [key, entry] of this.entries) if (!entry.users) {
      this.entries.delete(key); this.dispose(entry.value)
    }
  }
  private trim() {
    let total = this.sizeBytes
    for (const [key, entry] of this.entries) {
      if (total <= this.budget) break
      if (entry.users) continue
      this.entries.delete(key); total -= entry.bytes; this.dispose(entry.value)
    }
  }
}
