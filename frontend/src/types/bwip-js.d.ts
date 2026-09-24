declare module 'bwip-js' {
  type RenderOptions = {
    bcid: string
    text: string
    scale?: number
    height?: number
    padding?: number
    paddingwidth?: number
    paddingheight?: number
    backgroundcolor?: string
    includetext?: boolean
  }

  export function toCanvas(
    canvas: HTMLCanvasElement,
    opts: RenderOptions,
  ): void

  export function toBuffer(opts: RenderOptions): Promise<Buffer>
}
