import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, SearchBar, Skeleton } from 'antd-mobile'
import AppNavBar from '../components/AppNavBar'
import EmptyState from '../components/EmptyState'
import LazyImage from '../components/LazyImage'
import { dishRepository } from '../services'
import { Dish } from '../data/types'

export default function SearchView() {
  const [keyword, setKeyword] = useState('')
  const [results, setResults] = useState<Dish[]>([])
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    const timer = setTimeout(() => {
      const kw = keyword.trim()
      if (!kw) {
        setResults([])
        setLoading(false)
        return
      }
      setLoading(true)
      dishRepository.searchDishes(kw).then(data => {
        setResults(data)
        setLoading(false)
      })
    }, 300)
    return () => clearTimeout(timer)
  }, [keyword])

  return (
    <div className='page'>
      <AppNavBar title='搜索' />
      <div className='search-bar'>
        <SearchBar placeholder='搜索菜品 / 食材 / 调料' value={keyword} onChange={setKeyword} />
      </div>
      <div className='search-results'>
        {loading && <Skeleton.Title animated />}
        {!loading && keyword.trim() && results.length === 0 && <EmptyState description='未找到相关菜品' />}
        {!loading && results.map(dish => (
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