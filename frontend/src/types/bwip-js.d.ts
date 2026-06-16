declare module 'bwip-js' {
  export function toCanvas(
    canvas: HTMLCanvasElement,
    opts: {
      bcid: string
      text: string
      scale?: number
      height?: number
      includetext?: boolean
    },
  ): void
}
