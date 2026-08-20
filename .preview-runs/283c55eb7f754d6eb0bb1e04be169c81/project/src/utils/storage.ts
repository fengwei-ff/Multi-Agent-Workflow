const memoryStore = new Map<string, string>()

export function getStorage<T>(key: string, defaultValue: T): T {
  try {
    const value = window.localStorage.getItem(key)
    return value === null ? defaultValue : JSON.parse(value) as T
  } catch {
    const value = memoryStore.get(key)
    return value ? JSON.parse(value) as T : defaultValue
  }
}

export function setStorage(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
    memoryStore.delete(key)
  } catch {
    memoryStore.set(key, JSON.stringify(value))
  }
}