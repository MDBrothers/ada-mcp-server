with Ada.Text_IO;
with Utils;

procedure Main is
   Value : Integer := Utils.Add (10, 20);
begin
   Ada.Text_IO.Put_Line ("Result:" & Integer'Image (Value));
end Main;
