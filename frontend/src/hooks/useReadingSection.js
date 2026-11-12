import { useEffect, useState } from 'react'

// Track the last heading above the reading line, including long sections.
export function useReadingSection(ids) {
  const [current, setCurrent] = useState(null)
  useEffect(() => {
    let frame = 0
    const update = () => {
      frame = 0
      const headings = ids.map((id) => document.getElementById(id)).filter(Boolean)
      let selected = headings[0]
      for (const heading of headings) {
        if (heading.getBoundingClientRect().top <= 140) selected = heading
        else break
      }
      setCurrent(selected?.id || null)
    }
    const schedule = () => { if (!frame) frame = requestAnimationFrame(update) }
    window.addEventListener('scroll', schedule, { passive: true })
    window.addEventListener('resize', schedule)
    const observer = new ResizeObserver(schedule)
    const content = document.querySelector('.reader-document')
    if (content) observer.observe(content)
    schedule()
    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      window.removeEventListener('scroll', schedule)
      window.removeEventListener('resize', schedule)
    }
  }, [ids])
  return current
}
