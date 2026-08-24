/** Build a self-contained SVG image suitable for compositing over the live WebGL canvas. */
export function buildAnnotationSvgDataUrl(
  overlay: SVGSVGElement,
  width: number,
  height: number,
) {
  const clone = overlay.cloneNode(true) as SVGSVGElement
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  clone.setAttribute('width', String(width))
  clone.setAttribute('height', String(height))
  clone.setAttribute('data-render-context', 'viewport-canvas')
  const source = new XMLSerializer().serializeToString(clone)
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(source)}`
}

/**
 * Preserve the live camera pixels and visible vector overlay in one PNG.
 * Callers should pass the exact WebGL canvas used by the current viewport.
 */
export async function captureViewportWithAnnotations(
  viewport: HTMLCanvasElement,
  overlay: SVGSVGElement | null,
): Promise<string> {
  const composite = document.createElement('canvas')
  composite.width = viewport.width
  composite.height = viewport.height
  const context = composite.getContext('2d')
  if (!context) throw new Error('A 2D canvas is required to capture viewport annotations')
  context.drawImage(viewport, 0, 0, composite.width, composite.height)
  if (overlay && overlay.getAttribute('aria-hidden') !== 'true') {
    const image = await loadImage(buildAnnotationSvgDataUrl(overlay, composite.width, composite.height))
    context.drawImage(image, 0, 0, composite.width, composite.height)
  }
  return composite.toDataURL('image/png')
}

function loadImage(source: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error('Annotation SVG could not be composed into the capture'))
    image.src = source
  })
}
