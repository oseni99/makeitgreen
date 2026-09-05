import { useUser } from '@clerk/react'
import { Link } from 'react-router-dom'

export function ProfileLink() {
  const { isLoaded, isSignedIn, user } = useUser()

  if (!isLoaded || !isSignedIn || !user) return null

  return (
    <Link
      to="/profile"
      className="grid size-11 place-items-center rounded-full outline-none transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      aria-label="Open profile"
    >
      <img className="size-8 rounded-full object-cover" src={user.imageUrl} alt="" />
    </Link>
  )
}
