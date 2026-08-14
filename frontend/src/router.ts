import { createRouter, createWebHashHistory } from 'vue-router'

export enum R {
  EXPLORE = 'EXPLORE',
  INDEX = 'INDEX',
  PARASPACE = 'PARASPACE'
}

export const history = createWebHashHistory()
export const router = createRouter({
  history,
  routes: [
    {
      path: '',
      redirect: { name: R.EXPLORE }
    },
    {
      // Module 1: ensemble data exploration (default home page)
      path: '/explore',
      name: R.EXPLORE,
      component: () => import('./views/Exploration.vue')
    },
    {
      // Module 2: NN surrogate uncertainty prediction
      path: '/index',
      name: R.INDEX,
      component: () => import('./views/Index.vue')
    },
    {
      // Module 3: parameter space exploration (placeholder, under development)
      path: '/paraspace',
      name: R.PARASPACE,
      component: () => import('./views/ParaSpace.vue')
    },
  ]
})
