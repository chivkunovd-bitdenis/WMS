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
      const parts = d.map((x: { msg?: string; loc?: unknown }) =>
        typeof x?.msg === 'string' ? x.msg : JSON.stringify(x),
      )
      return parts.join('; ')
    }
    return text.slice(0, 200)
  } catch {
    return `Ошибка ${res.status}`
  }
}

