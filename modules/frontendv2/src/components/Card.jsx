export default function Card({ children, className = '', ...props }) {
  return (
    <div className={`card p-4 sm:p-6 ${className}`} {...props}>
      {children}
    </div>
  )
}

export function CardHeader({ children, className = '' }) {
  return (
    <div className={`mb-4 ${className}`}>
      {children}
    </div>
  )
}

export function CardTitle({ children, className = '', as: Heading = 'h3' }) {
  return (
    <Heading className={`text-base font-semibold text-gray-900 ${className}`}>
      {children}
    </Heading>
  )
}

export function CardContent({ children, className = '' }) {
  return (
    <div className={className}>
      {children}
    </div>
  )
}
