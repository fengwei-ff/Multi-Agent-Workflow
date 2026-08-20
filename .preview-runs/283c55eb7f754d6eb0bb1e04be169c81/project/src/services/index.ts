import { cuisines } from '../data/cuisine.data'
import { dishes, seedComments } from '../data/dish.data'
import { Cuisine, Dish, FoodComment } from '../data/types'
import { getStorage, setStorage } from '../utils/storage'

const delay = <T,>(data: T, ms = 200) => new Promise<T>((resolve) => setTimeout(() => resolve(data), ms))

export const cuisineRepository = {
  async getCuisines(): Promise<Cuisine[]> {
    return delay(cuisines)
  },
  async getCuisineById(id: string): Promise<Cuisine | undefined> {
    return delay(cuisines.find(c => c.id === id))
  }
}

export const dishRepository = {
  async getDishesByCuisine(cuisineId: string): Promise<Dish[]> {
    return delay(dishes.filter(d => d.cuisineId === cuisineId))
  },
  async getDishById(id: string): Promise<Dish | undefined> {
    return delay(dishes.find(d => d.id === id))
  },
  async searchDishes(keyword: string): Promise<Dish[]> {
    const kw = keyword.trim().toLowerCase()
    if (!kw) return []
    return delay(dishes.filter(d => {
      const haystack = [
        d.name, d.description,
        ...d.ingredients.map(i => i.name),
        ...d.steps.map(s => s.text)
      ].join(' ').toLowerCase()
      return haystack.includes(kw)
    }))
  }
}

export const commentRepository = {
  async getComments(dishId: string): Promise<FoodComment[]> {
    const localComments = getStorage<FoodComment[]>('msyt_comments', [])
    const result = [...seedComments.filter(c => c.dishId === dishId), ...localComments.filter(c => c.dishId === dishId)]
    result.sort((a, b) => b.createdAt.localeCompare(a.createdAt))
    return delay(result)
  },
  async addComment(comment: FoodComment): Promise<void> {
    const comments = getStorage<FoodComment[]>('msyt_comments', [])
    comments.push(comment)
    setStorage('msyt_comments', comments)
    return delay(void 0, 100)
  }
}

export const favoriteRepository = {
  async getFavoriteIds(): Promise<string[]> {
    return delay(getStorage<string[]>('msyt_favorites', []))
  },
  async addFavorite(dishId: string): Promise<void> {
    const ids = getStorage<string[]>('msyt_favorites', [])
    if (!ids.includes(dishId)) {
      ids.push(dishId)
      setStorage('msyt_favorites', ids)
    }
    return delay(void 0, 100)
  },
  async removeFavorite(dishId: string): Promise<void> {
    const ids = getStorage<string[]>('msyt_favorites', [])
    setStorage('msyt_favorites', ids.filter(id => id !== dishId))
    return delay(void 0, 100)
  }
}

export const userRepository = {
  getNickname(): string {
    return getStorage('msyt_nickname', '')
  },
  setNickname(nickname: string): void {
    setStorage('msyt_nickname', nickname)
  }
}