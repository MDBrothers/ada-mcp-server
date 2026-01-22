-- File with intentional errors for testing diagnostics
with Ada.Text_IO;

procedure Broken is
   X : Integer := "not an integer";  -- Type error: String vs Integer
   Y : Undefined_Type;               -- Error: undefined type
begin
   Ada.Text_IO.Put_Line (X);         -- Type error: Integer vs String
   Unknown_Procedure;                 -- Error: undefined procedure
end Broken;
