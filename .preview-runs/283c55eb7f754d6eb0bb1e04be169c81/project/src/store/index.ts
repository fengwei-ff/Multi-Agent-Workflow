import { configureStore } from '@reduxjs/toolkit'
import {
  cuisineReducer,
  dishReducer,
  favoriteReducer,
  commentReducer,
  userReducer
} from './slices'

const store = configureStore({
  reducer: {
    cuisine: cuisineReducer,
    dish: dishReducer,
    favorite: favoriteReducer,
    comment: commentReducer,
    user: userReducer
  }
})

export type RootState = ReturnType<typeof store.getState>
export type AppDispatch = typeof store.dispatch
export default store