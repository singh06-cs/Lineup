import { createContext } from 'react'

// Context makes the logged-in user available to any component without passing it
// down through props at every level.
export const AuthContext = createContext(null)
