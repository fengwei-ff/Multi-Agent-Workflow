import { createSlice, PayloadAction } from '@reduxjs/toolkit'
import { Cuisine, Dish, FoodComment } from '../data/types'

const cuisineSlice = createSlice({
  name: 'cuisine',
  initialState: { cuisines: [] as Cuisine[], loading: false },
  reducers: {
    setCuisines(state, action: PayloadAction<Cuisine[]>) {
      state.cuisines = action.payload
    },
    setLoading(state, action: PayloadAction<boolean>) {
      state.loading = action.payload
    }
  }
})
export const { setCuisines, setLoading } = cuisineSlice.actions
export const cuisineReducer = cuisineSlice.reducer

const dishSlice = createSlice({
  name: 'dish',
  initialState: {
    dishesByCuisine: {} as Record<string, Dish[]>,
    currentDish: null as Dish | null
  },
  reducers: {
    setDishes(state, action: PayloadAction<{ cuisineId: string; dishes: Dish[] }>) {
      state.dishesByCuisine[action.payload.cuisineId] = action.payload.dishes
    },
    setCurrentDish(state, action: PayloadAction<Dish>) {
      state.currentDish = action.payload
    },
    clearCurrentDish(state) {
      state.currentDish = null
    }
  }
})
export const { setDishes, setCurrentDish, clearCurrentDish } = dishSlice.actions
export const dishReducer = dishSlice.reducer

const favoriteSlice = createSlice({
  name: 'favorite',
  initialState: { favoriteIds: [] as string[] },
  reducers: {
    setFavoriteIds(state, action: PayloadAction<string[]>) {
      state.favoriteIds = action.payload
    },
    toggleFavoriteLocal(state, action: PayloadAction<string>) {
      const id = action.payload
      if (state.favoriteIds.includes(id)) {
        state.favoriteIds = state.favoriteIds.filter(fid => fid !== id)
      } else {
        state.favoriteIds.push(id)
      }
    }
  }
})
export const { setFavoriteIds, toggleFavoriteLocal } = favoriteSlice.actions
export const favoriteReducer = favoriteSlice.reducer

interface CommentState {
  commentsByDish: Record<string, FoodComment[]>
}

const commentSlice = createSlice({
  name: 'comment',
  initialState: { commentsByDish: {} } as CommentState,
  reducers: {
    setComments(state, action: PayloadAction<{ dishId: string; comments: FoodComment[] }>) {
      state.commentsByDish[action.payload.dishId] = action.payload.comments
    },
    appendComment(state, action: PayloadAction<FoodComment>) {
      const { dishId } = action.payload
      if (!state.commentsByDish[dishId]) state.commentsByDish[dishId] = []
      state.commentsByDish[dishId].unshift(action.payload)
    }
  }
})
export const { setComments, appendComment } = commentSlice.actions
export const commentReducer = commentSlice.reducer

const userSlice = createSlice({
  name: 'user',
  initialState: { nickname: '' },
  reducers: {
    setNickname(state, action: PayloadAction<string>) {
      state.nickname = action.payload
    }
  }
})
export const { setNickname } = userSlice.actions
export const userReducer = userSlice.reducer