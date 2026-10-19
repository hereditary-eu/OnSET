import { createRouter, createWebHistory } from 'vue-router'
import ConfigSelectView from '@/views/ConfigSelectView.vue'
import { listConfigs, setActiveConfig } from '@/utils/api'
import { OntoConfig } from '@/utils/sparql/ontoconfig'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'configs',
      component: ConfigSelectView
    },
    // Every page below operates on the configuration given by the first path segment
    {
      path: '/:configId',
      redirect: to => ({ name: 'explore', params: to.params })
    },
    {
      path: '/:configId/explore',
      name: 'explore',
      component: () => import('@/views/OntologyExplorative.vue')
    },
    {
      path: '/:configId/circles',
      name: 'circles',
      component: () => import('@/views/3D-Circles.vue')
    },
    {
      path: '/:configId/graph',
      name: 'graph',
      component: () => import('@/views/OntologyGraph.vue')
    },
    {
      path: '/:configId/linked-circles',
      name: 'linked-circles',
      component: () => import('@/views/LinkedOntology.vue')
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/'
    }
  ]
})

// Activate the configuration addressed by the route before any page (and thus any API call) runs
router.beforeEach(async (to) => {
  const configId = to.params.configId as string | undefined
  if (!configId) {
    setActiveConfig(null)
    return true
  }
  try {
    const configs = await listConfigs()
    if (!configs.some(c => c.id === configId)) {
      return { name: 'configs', query: { unknown: configId } }
    }
    setActiveConfig(configId)
    await OntoConfig.ensureConfig()
    return true
  } catch (e) {
    console.error(`Failed to load configuration '${configId}'`, e)
    setActiveConfig(null)
    return { name: 'configs', query: { failed: configId } }
  }
})

export default router
