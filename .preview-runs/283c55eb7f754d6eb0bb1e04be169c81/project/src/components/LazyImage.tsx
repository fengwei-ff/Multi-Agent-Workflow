import { useEffect, useRef, useState } from 'react'

export default function LazyImage({ src, alt, ...rest }: React.ImgHTMLAttributes<HTMLImageElement>) {
  const [visible, setVisible] = useState(false)
  const imgRef = useRef<HTMLImageElement>(null)

  useEffect(() => {
    const el = imgRef.current
    if (!el) return
    if (typeof IntersectionObserver === 'undefined') {
      setVisible(true)
      return
    }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          setVisible(true)
          observer.disconnect()
        }
      })
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return <img ref={imgRef} src={visible ? src : undefined} alt={alt || ''} {...rest} />
}