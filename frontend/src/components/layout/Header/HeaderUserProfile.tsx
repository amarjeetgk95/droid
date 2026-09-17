'use client';

/**
 * Header account control.
 *
 * The Auth module owns the hardened menu (sign-out confirmation, pending
 * state, visible failure); `Header.tsx` keeps importing `HeaderUserProfile`
 * unchanged while rendering `UserProfileMenu`.
 */
export { UserProfileMenu as HeaderUserProfile } from '@/components/auth/UserProfileMenu';
