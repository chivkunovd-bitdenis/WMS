// WMS-566: звук сканера на складе — короткий высокий на удачный скан,
// низкий двойной на неудачный (товар не найден, ошибка сервера).
// Браузер без звука или с запретом автозвука просто молчит.

let audioContext: AudioContext | null = null

function tone(ctx: AudioContext, frequency: number, startAt: number, durationSec: number): void {
  const oscillator = ctx.createOscillator()
  const gain = ctx.createGain()
  oscillator.type = 'square'
  oscillator.frequency.value = frequency
  gain.gain.setValueAtTime(0.08, startAt)
  gain.gain.exponentialRampToValueAtTime(0.0001, startAt + durationSec)
  oscillator.connect(gain).connect(ctx.destination)
  oscillator.start(startAt)
  oscillator.stop(startAt + durationSec)
}

function play(render: (ctx: AudioContext, now: number) => void): void {
  try {
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!Ctor) return
    audioContext ??= new Ctor()
    if (audioContext.state === 'suspended') void audioContext.resume()
    render(audioContext, audioContext.currentTime)
  } catch {
    // Звук — только подсказка; скан от него не зависит.
  }
}

export function playScanSuccess(): void {
  play((ctx, now) => tone(ctx, 1800, now, 0.08))
}

export function playScanError(): void {
  play((ctx, now) => {
    tone(ctx, 220, now, 0.18)
    tone(ctx, 180, now + 0.24, 0.3)
  })
}
