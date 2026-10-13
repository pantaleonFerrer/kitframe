package auth

import "testing"

func TestHashAndVerifyPassword(t *testing.T) {
	hash, err := HashPassword("Password123!")
	if err != nil {
		t.Fatal(err)
	}
	ok, err := VerifyPassword(hash, "Password123!")
	if err != nil || !ok {
		t.Fatalf("verify failed: %v %v", ok, err)
	}
	ok, err = VerifyPassword(hash, "WrongPassword!")
	if err != nil {
		t.Fatal(err)
	}
	if ok {
		t.Fatal("wrong password should fail")
	}
}

func TestPasswordTooShort(t *testing.T) {
	_, err := HashPassword("short")
	if err == nil {
		t.Fatal("expected error")
	}
}
