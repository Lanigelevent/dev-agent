package stack

import "testing"

func TestPushPopSize(t *testing.T) {
	s := &Stack{}
	s.Push(1)
	s.Push(2)
	if s.Size() != 2 {
		t.Fatalf("Size=%d, want 2", s.Size())
	}
	if got := s.Pop(); got != 2 {
		t.Fatalf("Pop=%d, want 2", got)
	}
	if s.Size() != 1 {
		t.Fatalf("Size after pop=%d, want 1", s.Size())
	}
}
