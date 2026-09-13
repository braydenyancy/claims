import { createRouter, createWebHistory } from "vue-router";
import { useSession } from "./composables/useSession";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/claims" },
    { path: "/login", name: "login", component: () => import("./views/LoginView.vue") },
    { path: "/claims", name: "claims", component: () => import("./views/ClaimListView.vue") },
    {
      path: "/claims/:id",
      name: "claim",
      component: () => import("./views/ClaimDetailView.vue"),
      props: (route) => ({ id: Number(route.params.id) }),
    },
  ],
});

router.beforeEach(async (to) => {
  const session = useSession();
  const user = await session.load();
  if (to.name !== "login" && !user) return { name: "login", query: { next: to.fullPath } };
  if (to.name === "login" && user) return { name: "claims" };
});

export default router;
