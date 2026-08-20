import { useEffect, useState } from 'react'
import { useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import { Card } from 'antd-mobile'
import AppNavBar from '../components/AppNavBar'
import EmptyState from '../components/EmptyState'
import LazyImage from '../components/LazyImage'
import { RootState } from '../store'
import { dishRepository } from '../services'
import { Dish } from '../data/types'

export default function FavoritesView() {
  const favoriteIds = useSelector((state: RootState) => state.favorite.favoriteIds)
  const navigate = useNavigate()
  const [dishes, setDishes] = useState<Dish[]>([])

  useEffect(() => {
    Promise.all(favoriteIds.map(id => dishRepository.getDishById(id))).then(list => {
      setDishes(list.filter(Boolean) as Dish[])
    })
  }, [favoriteIds])

  return (
    <div className='page'>
      <AppNavBar title='我的收藏' />
      {dishes.length === 0 ? <EmptyState description='暂无收藏，去逛逛吧~' /> : dishes.map(dish => (
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
  )
}