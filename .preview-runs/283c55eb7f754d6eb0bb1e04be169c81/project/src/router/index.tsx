import { HashRouter, Routes, Route } from 'react-router-dom'
import HomeView from '../views/HomeView'
import DishListView from '../views/DishListView'
import DishDetailView from '../views/DishDetailView'
import SearchView from '../views/SearchView'
import FavoritesView from '../views/FavoritesView'
import { useDispatch } from 'react-redux'
import { useEffect } from 'react'
import { setFavoriteIds, setNickname } from '../store/slices'
import { favoriteRepository, userRepository } from '../services'

export default function AppRouter() {
  const dispatch = useDispatch()
  useEffect(() => {
    favoriteRepository.getFavoriteIds().then(ids => dispatch(setFavoriteIds(ids)))
    const nick = userRepository.getNickname()
    if (nick) dispatch(setNickname(nick))
  }, [dispatch])

  return (
    <HashRouter>
      <Routes>
        <Route path='/' element={<HomeView />} />
        <Route path='/cuisine/:cuisineId' element={<DishListView />} />
        <Route path='/dish/:dishId' element={<DishDetailView />} />
        <Route path='/search' element={<SearchView />} />
        <Route path='/favorites' element={<FavoritesView />} />
      </Routes>
    </HashRouter>
  )
}