import { NavBar } from 'antd-mobile'
import { useNavigate, useLocation } from 'react-router-dom'

interface Props {
  title?: string
  right?: React.ReactNode
}

export default function AppNavBar({ title = '教学美食', right }: Props) {
  const navigate = useNavigate()
  const location = useLocation()
  const showBack = location.pathname !== '/'

  return (
    <NavBar
      onBack={showBack ? () => navigate(-1) : undefined}
      right={right}
    >
      {title}
    </NavBar>
  )
}