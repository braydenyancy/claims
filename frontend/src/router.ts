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
  // load() rethrows on anything but a 403 (network down, 500); treat that as
  // signed out too, so the guard still redirects instead of leaving a blank page.
  let user;
  try {
    user = await session.load();
  } catch {
    user = null;
  }
  if (to.name !== "login" && !user) return { name: "login", query: { next: to.fullPath } };
  if (to.name === "login" && user) return { name: "claims" };
});

export default router;
