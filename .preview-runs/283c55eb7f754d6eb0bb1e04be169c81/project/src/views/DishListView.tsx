import { useEffect } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate, useParams } from 'react-router-dom'
import { Card } from 'antd-mobile'
import AppNavBar from '../components/AppNavBar'
import LazyImage from '../components/LazyImage'
import EmptyState from '../components/EmptyState'
import { RootState } from '../store'
import { setDishes } from '../store/slices'
import { dishRepository } from '../services'

export default function DishListView() {
  const { cuisineId = '' } = useParams()
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const dishes = useSelector((state: RootState) => state.dish.dishesByCuisine[cuisineId] || [])

  useEffect(() => {
    dishRepository.getDishesByCuisine(cuisineId).then(data => {
      dispatch(setDishes({ cuisineId, dishes: data }))
    })
  }, [cuisineId, dispatch])

  return (
    <div className='page'>
      <AppNavBar title='菜品列表' />
      <div className='dish-list'>
        {dishes.length === 0 ? <EmptyState description='暂无菜品' /> : dishes.map(dish => (
          <Card key={dish.id} onClick={() => navigate(`/dish/${dish.id}`)}>
            <div className='dish-row'>
              <LazyImage src={dish.thumbnail} alt={dish.name} className='dish-thumb' />
              <div className='dish-info'>
                <div className='dish-name'>{dish.name}</div>
                <div className='dish-description'>{dish.description}</div>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}