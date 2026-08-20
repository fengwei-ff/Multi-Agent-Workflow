import { useEffect } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import { Card } from 'antd-mobile'
import AppNavBar from '../components/AppNavBar'
import LazyImage from '../components/LazyImage'
import { RootState } from '../store'
import { setCuisines } from '../store/slices'
import { cuisineRepository } from '../services'

export default function HomeView() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const cuisines = useSelector((state: RootState) => state.cuisine.cuisines)

  useEffect(() => {
    cuisineRepository.getCuisines().then(data => {
      dispatch(setCuisines(data))
    })
  }, [dispatch])

  return (
    <div className='page'>
      <AppNavBar right={<span onClick={() => navigate('/favorites')} style={{ cursor: 'pointer' }}>收藏</span>} />
      <div className='cuisine-grid'>
        {cuisines.map(c => (
          <div key={c.id} onClick={() => navigate(`/cuisine/${c.id}`)}>
            <Card>
              <LazyImage src={c.image} alt={c.name} />
              <div className='cuisine-name'>{c.name}</div>
              <div className='cuisine-desc'>{c.description}</div>
            </Card>
          </div>
        ))}
      </div>
    </div>
  )
}