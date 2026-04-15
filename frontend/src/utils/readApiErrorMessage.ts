export async function readApiErrorMessage(res: Response): Promise<string> {
  try {
    const text = await res.text()
    if (!text) {
      return `Ошибка ${res.status}`
    }
    const data = JSON.parse(text) as { detail?: unknown }
    const d = data.detail
    if (typeof d === 'string') {
      return d
    }
    if (Array.isArray(d)) {
      const parts = d
        .map((x: { msg?: string; loc?: unknown }) => {
          const msg = typeof x?.msg === 'string' ? x.msg : null
          const loc = x?.loc
          const field =
            Array.isArray(loc) && loc.length > 0
              ? String(loc[loc.length - 1])
              : null
          if (msg && field) return `${field}: ${msg}`
          if (msg) return msg
          return JSON.stringify(x)
        })
        .filter((p): p is string => Boolean(p))
      // FastAPI/Pydantic часто возвращают много строк — ограничим длину.
      return parts.join('; ').slice(0, 240)
    }
    return text.slice(0, 200)
  } catch {
    return `Ошибка ${res.status}`
  }
}

